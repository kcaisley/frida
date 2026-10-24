"""The delay line and ring oscillator's design space (``flow.sweep``): the characterization's seven
chains at up to seven sizes, in every PDK.

Each instance at the core supply and the nominal control (8/12 of it): a ring's frequency,
swing, power and energy per cycle, a delay line's rise and fall
delays and output transitions and its energy per input cycle (4 ns period), either one's delay per
stage; over the supply (90 to 120 % of its own) the same. A chain with a control (starved or on a
shared tail) also over the control, 5/12 of the supply to all of it, and its tuning gain about
the nominal control. Four to twelve Spectre runs of 40 ns, under a minute.
"""

from __future__ import annotations

import importlib
import math
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.pipeline import Plot, Record

from .sim import CONTROL_SWEEP, NOMINAL_CONTROL, DelayTbParams, _run_delay_sim, delay_signal_names
from .subckt import CASES, Control, Delay, DelayParams, Stage, is_valid_delay_params, write_netlist

GENERATOR = Delay
# the characterization's lines and rings (flow.delay.subckt.CASES)
STRUCTURE = ("stage", "control", "stages", "differential", "ring", "inject")
STRUCTURES = [{key: getattr(case, key) for key in STRUCTURE} for case in CASES.values()]
# every width scaled together (x0.5 to x4); the coupling inverters alone doubled (coupled stages
# only); the starving devices and the tail doubled (controlled chains only); the stage inverters
# at twice their length
NOMINAL = DelayParams()
WIDTHS = ("inv_n_w", "inv_p_w", "fb_n_w", "fb_p_w", "starve_n_w", "starve_p_w", "tail_w", "en_w", "inj_w")
COUPLING = {name: 2 * getattr(NOMINAL, name) for name in ("fb_n_w", "fb_p_w")}
CONTROLS = {name: 2 * getattr(NOMINAL, name) for name in ("starve_n_w", "starve_p_w", "tail_w")}
SIZES = [
    {name: max(1, getattr(NOMINAL, name) // 2) for name in WIDTHS},
    {},
    {name: 2 * getattr(NOMINAL, name) for name in WIDTHS},
    {name: 4 * getattr(NOMINAL, name) for name in WIDTHS},
    COUPLING,
    CONTROLS,
    {"inv_l": 2 * NOMINAL.inv_l},
]
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
# the tuning gain from the control points either side of the nominal
GAIN_POINTS = (7 / 12, 9 / 12)


def instances(pdk: str) -> list[DelayParams]:
    """Every line at every size it has devices for (coupling inverters only in coupled stages,
    starving devices or a tail only in controlled ones), in every PDK."""
    delays = (
        DelayParams(**structure, **sizes)
        for structure in STRUCTURES
        for sizes in SIZES
        if not (sizes is COUPLING and structure["stage"] != Stage.COUPLED)
        and not (sizes is CONTROLS and structure["control"] == Control.NONE)
    )
    return [delay for delay in delays if is_valid_delay_params(delay)]


def _measure(run_dir: Path, tb: DelayTbParams):
    """One Spectre run of the chain's testbench, as a measurement."""

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave
    from flow.delay.analysis import MeasDelay

    raw = _run_delay_sim(run_dir, tb)
    interval = tb.waveform_sample_interval_s
    wave, points = read_transient_wave(raw, delay_signal_names(), interval, supply_rails=("vdd",))
    measurement = MeasDelay(
        group=None,
        index=None,
        dut=tb.delay,
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


def characterize(run_dir: Path, pdk: str, delay: DelayParams) -> Record:
    from flow.analysis.io import write_measurement
    from flow.delay.analysis import analyze_delay_oscillation, analyze_delay_propagation

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    def bench(vdd: float, control: float) -> DelayTbParams:
        return DelayTbParams(pdk=pdk, delay=delay, vdd=round(vdd, 4), control_v=round(control, 4))

    supplies = [
        _measure(run_dir / f"supply_{round(factor * 100)}", bench(factor * supply, NOMINAL_CONTROL * supply))
        for factor in SUPPLY_SWEEP
    ]
    at = SUPPLY_SWEEP.index(1.0)
    nominal = supplies[at]
    controlled = delay.control != Control.NONE
    controls = [
        nominal
        if math.isclose(step, NOMINAL_CONTROL)
        else _measure(run_dir / f"control_{round(step * 12)}", bench(supply, step * supply))
        for step in (CONTROL_SWEEP if controlled else ())
    ]
    path = run_dir / "supply_100" / "result.h5"
    write_measurement(path, nominal)
    waves = {"nominal": str(path.relative_to(Path(__file__).resolve().parents[2]))}

    if delay.ring:
        over_supply = analyze_delay_oscillation(supplies)
        # a ring's period is two passes around it, each a delay per stage
        stage_delay = 1 / (2 * delay.stages * over_supply.frequency_hz)
        energy, power = over_supply.energy_per_cycle_j, over_supply.power_w
        metrics = {
            "frequency_hz": float(over_supply.frequency_hz[at]),
            "swing_v": float(over_supply.swing_v[at]),
            "delay_rise_s": math.nan,
            "delay_fall_s": math.nan,
            "transition_rise_s": math.nan,
            "transition_fall_s": math.nan,
        }
        details = [
            Plot(
                name="frequency_supply",
                title="Ring frequency over the supply (control 8/12 of the core supply)",
                x_label="Supply over nominal",
                y_label="Frequency (Hz)",
                x=list(SUPPLY_SWEEP),
                series={"frequency": list(over_supply.frequency_hz)},
            )
        ]
    else:
        over_supply = analyze_delay_propagation(supplies)
        stage_delay = (over_supply.rise_delay_s + over_supply.fall_delay_s) / (2 * delay.stages)
        energy, power = over_supply.energy_per_cycle_j, over_supply.vdd_v * over_supply.supply_current_a
        metrics = {
            "frequency_hz": math.nan,
            "swing_v": math.nan,
            "delay_rise_s": float(over_supply.rise_delay_s[at]),
            "delay_fall_s": float(over_supply.fall_delay_s[at]),
            "transition_rise_s": float(over_supply.output_rise_s[at]),
            "transition_fall_s": float(over_supply.output_fall_s[at]),
        }
        details = [
            Plot(
                name="delay_supply",
                title="Line delay over the supply (control 8/12 of the core supply)",
                x_label="Supply over nominal",
                y_label="Delay (s)",
                x=list(SUPPLY_SWEEP),
                series={
                    "rising input": list(over_supply.rise_delay_s),
                    "falling input": list(over_supply.fall_delay_s),
                },
            )
        ]
    metrics |= {
        "stage_delay_s": float(stage_delay[at]),
        "power_w": float(power[at]),
        "energy_per_cycle_j": float(energy[at]),
        "stage_delay_max_supply_s": float(np.nanmax(stage_delay)),
        "tuning_gain_hz_per_v": math.nan,
        "delay_gain_s_per_v": math.nan,
    }
    details += [
        Plot(
            name="stage_delay_supply",
            title="Delay per stage over the supply",
            x_label="Supply over nominal",
            y_label="Delay per stage (s)",
            x=list(SUPPLY_SWEEP),
            series={"stage delay": list(stage_delay)},
        ),
        Plot(
            name="energy_supply",
            title="Energy per cycle over the supply" if delay.ring else "Energy per input cycle over the supply",
            x_label="Supply over nominal",
            y_label="Energy per cycle (J)",
            x=list(SUPPLY_SWEEP),
            series={"energy": list(energy)},
        ),
    ]

    if controlled:
        control_v = [step * supply for step in CONTROL_SWEEP]
        low, high = (next(i for i, step in enumerate(CONTROL_SWEEP) if math.isclose(step, p)) for p in GAIN_POINTS)
        span = control_v[high] - control_v[low]
        if delay.ring:
            over_control = analyze_delay_oscillation(controls)
            metrics["tuning_gain_hz_per_v"] = float(
                (over_control.frequency_hz[high] - over_control.frequency_hz[low]) / span
            )
            details.append(
                Plot(
                    name="frequency_control",
                    title="Ring frequency over the control (core supply)",
                    x_label="Control (V)",
                    y_label="Frequency (Hz)",
                    x=control_v,
                    series={"frequency": list(over_control.frequency_hz)},
                )
            )
        else:
            over_control = analyze_delay_propagation(controls)
            line = (over_control.rise_delay_s + over_control.fall_delay_s) / 2
            metrics["delay_gain_s_per_v"] = float((line[high] - line[low]) / span)
            details.append(
                Plot(
                    name="delay_control",
                    title="Line delay over the control (core supply)",
                    x_label="Control (V)",
                    y_label="Delay (s)",
                    x=control_v,
                    series={
                        "rising input": list(over_control.rise_delay_s),
                        "falling input": list(over_control.fall_delay_s),
                    },
                )
            )
        details.append(
            Plot(
                name="energy_control",
                title="Energy per cycle over the control (core supply)",
                x_label="Control (V)",
                y_label="Energy per cycle (J)",
                x=control_v,
                series={"energy": list(over_control.energy_per_cycle_j)},
            )
        )

    return Record(metrics=metrics, details=details, waves=waves)


def layout_netlist(out_dir: Path, pdk: str, delay: DelayParams) -> Path:
    """The all-transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``)."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(delay, out_dir / "delay_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "delay.sp")
