"""The CML gates' design space (``flow.sweep``): the characterization's five gates at seven
sizings, in every PDK.

Each instance at the nominal point (a 200 ps clock, the data at 2.6 clock periods, its own core
supply): the single-ended swing, output common mode, delay, the share of checked instants where
the output holds its function's value, and the supply current. The tail current scales with the
tail's width (30 uA at the generator's default), so a wider gate draws more. Over the clock
period (1 ns to 25 ps) and the tail current (a sixth to 3.3 times its own) the swing, delay and
correctness; over the supply (90 to 120 % of its own) the swing and delay; the differential
output folded on the driving input's edges (the eye). Delays only where the output is correct.
Twenty-one Spectre runs, about a minute in all.
"""

from __future__ import annotations

import importlib
import math
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np
from hdl21.primitives import MosType

from flow.sweep import Detail, Record

from .sim import (
    CLOCK_PERIOD_SWEEP_S,
    NOMINAL_CLOCK_PERIOD_S,
    NOMINAL_TAIL_CURRENT_A,
    TAIL_CURRENT_SWEEP_A,
    CmlTbParams,
    _run_cml_sim,
    cml_signal_names,
)
from .subckt import CASES, Cml, CmlParams, Function, is_valid_cml_params, write_netlist

GENERATOR = Cml
TOPOLOGIES = {
    name: {"function": case.function, "input_xtors": case.input_xtors, "load": case.load}
    for name, case in CASES.items()
}
# the key devices' widths scaled together (x0.5 to x4), the input pair or the loads alone doubled,
# and the input pair and tail at twice their length
DEFAULT = CmlParams()
WIDTHS = ("in_w", "tail_w", "load_w")
SIZINGS = {
    "x0.5": {name: getattr(DEFAULT, name) // 2 for name in WIDTHS},
    "x1": {},
    "x2": {name: 2 * getattr(DEFAULT, name) for name in WIDTHS},
    "x4": {name: 4 * getattr(DEFAULT, name) for name in WIDTHS},
    "pair_x2": {"in_w": 2 * DEFAULT.in_w},
    "load_x2": {"load_w": 2 * DEFAULT.load_w},
    "long": {"in_l": 2 * DEFAULT.in_l, "tail_l": 2 * DEFAULT.tail_l},
}
TAIL_SWEEP = tuple(current / NOMINAL_TAIL_CURRENT_A for current in TAIL_CURRENT_SWEEP_A)
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
EYE_TRACES = 8


def params(pdk: str, topology: str, sizing: str) -> CmlParams | None:
    cml = CmlParams(**TOPOLOGIES[topology], **SIZINGS[sizing])
    return cml if is_valid_cml_params(cml) else None


def _measure(run_dir: Path, tb: CmlTbParams):
    """One Spectre transient of the CML testbench, as a measurement."""

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave

    from .analysis import MeasCml

    raw = _run_cml_sim(run_dir, tb)
    wave, points = read_transient_wave(raw, cml_signal_names(), tb.waveform_sample_interval_s, supply_rails=("vdd",))
    info = MeasInfo(
        backend="spice",
        timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
        instruments={"simulator": "Spectre"},
        readbacks={"raw_points": points, "supply_current_convention": "positive_current_draw"},
    )
    raw.unlink()  # the measurement keeps the waveforms
    return MeasCml(
        group=None, index=None, dut=tb.cml, info=info, param=tb, trial_index=np.arange(1, dtype=np.int64), wave=wave
    )


def _eye(measurement) -> tuple[list[float], dict[str, list[float]]]:
    """The differential output over the record's second half, one trace per edge of the input
    that drives it (the data for a buffer or an XOR, the clock for a latch or a divider), from half
    a bit before the edge to one and a half after; the bit is half that input's period."""

    from flow.analysis import calc

    tb, wave = measurement.param, measurement.wave
    trigger, period = (
        ("in", tb.data_period_s) if tb.cml.function in (Function.BUFFER, Function.XOR) else ("clk", tb.clock_period_s)
    )
    bit = float(period) / 2
    time_s = wave.time_s
    output = wave.v["outp"][0] - wave.v["outn"][0]
    edges = calc.cross(wave.v[f"{trigger}p"][0] - wave.v[f"{trigger}n"][0], time_s, 0.0, edge="either")
    edges = edges[(edges - bit / 2 > time_s[-1] / 2) & (edges + 1.5 * bit < time_s[-1])][:EYE_TRACES]
    phase = np.linspace(-bit / 2, 1.5 * bit, 81)
    return list(phase), {
        f"edge {k + 1}": list(calc.value(output, time_s, edge + phase)) for k, edge in enumerate(edges)
    }


def characterize(run_dir: Path, pdk: str, cml: CmlParams) -> Record:
    from flow.analysis.io import write_measurement

    from .analysis import analyze_cml_switching

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    tail = NOMINAL_TAIL_CURRENT_A * cml.tail_w / DEFAULT.tail_w

    def bench(vdd: float, period: float, current: float) -> CmlTbParams:
        # the CML levels across the supply's top third (a PMOS input: its bottom third)
        pmos = cml.input_xtors == MosType.PMOS
        levels = {"vhigh": vdd / 3, "vlow": 0.0} if pmos else {"vhigh": vdd, "vlow": 2 * vdd / 3}
        return CmlTbParams(
            pdk=pdk,
            cml=cml,
            vdd=round(vdd, 4),
            clock_period_s=period,
            data_period_s=2.6 * period,
            transition_time_s=min(20e-12, period / 5),
            tstop_s=20 * period + 0.5e-9,
            waveform_sample_interval_s=min(0.5e-12, period / 100),
            tail_current_a=current,
            **{key: round(value, 4) for key, value in levels.items()},
        )

    def point(folder: str, vdd: float, period: float, current: float):
        return _measure(run_dir / folder, bench(vdd, period, current))

    periods = {
        period: point(f"period_{round(period * 1e12)}ps", supply, period, tail) for period in CLOCK_PERIOD_SWEEP_S
    }
    nominal = periods[NOMINAL_CLOCK_PERIOD_S]
    currents = {
        factor: nominal
        if factor == 1.0
        else point(f"tail_{round(factor * tail * 1e9)}na", supply, NOMINAL_CLOCK_PERIOD_S, factor * tail)
        for factor in TAIL_SWEEP
    }
    supplies = {
        factor: nominal
        if factor == 1.0
        else point(f"supply_{round(factor * 100)}", factor * supply, NOMINAL_CLOCK_PERIOD_S, tail)
        for factor in SUPPLY_SWEEP
    }
    waves = {}
    for label, measurement in (("200 ps clock", nominal), ("50 ps clock", periods[50e-12])):
        path = run_dir / f"period_{round(float(measurement.param.clock_period_s) * 1e12)}ps" / "result.h5"
        write_measurement(path, measurement)
        waves[label] = str(path.relative_to(Path(__file__).resolve().parents[2]))
    over_period = analyze_cml_switching(list(periods.values()))
    over_tail = analyze_cml_switching(list(currents.values()))
    over_supply = analyze_cml_switching(list(supplies.values()))
    at = analyze_cml_switching([nominal])
    working = over_period.correct_fraction == 1.0
    tail_working = over_tail.correct_fraction == 1.0
    phase, eye = _eye(nominal)
    frequency = list(1 / over_period.clock_period_s)

    def delay(result) -> list[float]:
        # a stuck or wrong output's crossings are noise, not a delay
        return list(np.where(result.correct_fraction == 1.0, result.delay_s, math.nan))

    supply_delay = np.asarray(delay(over_supply))

    return Record(
        metrics={
            "swing_v": float(at.swing_v[0]),
            "output_cm_v": float(at.output_cm_v[0]),
            "delay_s": delay(at)[0],
            "correct_fraction": float(at.correct_fraction[0]),
            "tail_current_a": tail,
            "supply_current_a": float(at.supply_current_a[0]),
            "power_w": float(at.power_w[0]),
            "fmax_hz": float(np.max(1 / over_period.clock_period_s[working])) if working.any() else math.nan,
            "tail_min_a": float(np.min(over_tail.tail_current_a[tail_working])) if tail_working.any() else math.nan,
            "delay_max_supply_s": float(np.nanmax(supply_delay)) if np.isfinite(supply_delay).any() else math.nan,
        },
        details=[
            Detail(
                name="swing_frequency",
                title="Swing over the clock frequency (data at 1/2.6 of it)",
                x_label="Clock frequency (Hz)",
                y_label="Single-ended swing (V)",
                x=frequency,
                series={"swing": list(over_period.swing_v)},
                x_log=True,
            ),
            Detail(
                name="delay_frequency",
                title="Delay over the clock frequency",
                x_label="Clock frequency (Hz)",
                y_label="Delay from the driving input (s)",
                x=frequency,
                series={"delay": delay(over_period)},
                x_log=True,
            ),
            Detail(
                name="correct_frequency",
                title="Correct output over the clock frequency (1: it works)",
                x_label="Clock frequency (Hz)",
                y_label="Share of checked instants correct",
                x=frequency,
                series={"correct": list(over_period.correct_fraction)},
                x_log=True,
            ),
            Detail(
                name="swing_tail",
                title="Swing over the tail current (200 ps clock)",
                x_label="Tail current (A)",
                y_label="Single-ended swing (V)",
                x=list(over_tail.tail_current_a),
                series={"swing": list(over_tail.swing_v)},
                x_log=True,
            ),
            Detail(
                name="delay_tail",
                title="Delay over the tail current (200 ps clock)",
                x_label="Tail current (A)",
                y_label="Delay from the driving input (s)",
                x=list(over_tail.tail_current_a),
                series={"delay": delay(over_tail)},
                x_log=True,
            ),
            Detail(
                name="swing_supply",
                title="Swing over the supply",
                x_label="Supply over nominal",
                y_label="Single-ended swing (V)",
                x=list(SUPPLY_SWEEP),
                series={"swing": list(over_supply.swing_v)},
            ),
            Detail(
                name="delay_supply",
                title="Delay over the supply",
                x_label="Supply over nominal",
                y_label="Delay from the driving input (s)",
                x=list(SUPPLY_SWEEP),
                series={"delay": delay(over_supply)},
            ),
            Detail(
                name="eye",
                title="Eye: the differential output on the driving input's edges (200 ps clock)",
                x_label="Time from the input's edge (s)",
                y_label="Differential output (V)",
                x=phase,
                series=eye,
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, cml: CmlParams) -> Path:
    """The transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``), for ALIGN to lay out without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(cml, out_dir / "cml_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "cml.sp")
