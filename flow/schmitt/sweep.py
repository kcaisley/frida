"""The Schmitt trigger's design space (``flow.sweep``): the inverting trigger and the buffer at
eight sizings, in every PDK.

Each instance over the supply (90 to 120 % of its own): the slow triangle (1 us a ramp: the trip
points on the way up and down, their difference the hysteresis) and the step (4 ns period, 50 ps
edges: each edge's delay, the output's transitions and the energy per cycle), into 5 fF. The
nominal triangle also gives the transfer curve both ways. Eight Spectre runs, under half a minute.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.sweep import Detail, Record

from .sim import SchmittTbParams, _run_schmitt_sim, schmitt_signal_names
from .subckt import Schmitt, SchmittParams, is_valid_schmitt_params, write_netlist

GENERATOR = Schmitt
# the characterization's inv_wide (the feedback at twice its width) is the sizing fb_x2 here
TOPOLOGIES = {"inv": {"buffer": False}, "buffer": {"buffer": True}}
# every width scaled together (x0.5 to x4), the feedback devices alone from half to four times
# (narrower to wider hysteresis), and every device at twice its length
NOMINAL = SchmittParams()
WIDTHS = ("n_w", "p_w", "fb_n_w", "fb_p_w")
FEEDBACK = ("fb_n_w", "fb_p_w")
SIZINGS = {
    "x0.5": {name: max(1, getattr(NOMINAL, name) // 2) for name in WIDTHS},
    "x1": {},
    "x2": {name: 2 * getattr(NOMINAL, name) for name in WIDTHS},
    "x4": {name: 4 * getattr(NOMINAL, name) for name in WIDTHS},
    "fb_x0.5": {name: max(1, getattr(NOMINAL, name) // 2) for name in FEEDBACK},
    "fb_x2": {name: 2 * getattr(NOMINAL, name) for name in FEEDBACK},
    "fb_x4": {name: 4 * getattr(NOMINAL, name) for name in FEEDBACK},
    "long": {"l": 2 * NOMINAL.l},
}
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
TRANSFER_POINTS = 81


def params(pdk: str, topology: str, sizing: str) -> SchmittParams | None:
    schmitt = SchmittParams(**TOPOLOGIES[topology], **SIZINGS[sizing])
    return schmitt if is_valid_schmitt_params(schmitt) else None


def _measure(run_dir: Path, tb: SchmittTbParams):
    """One Spectre run of the trigger's testbench, as a measurement."""

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave
    from flow.schmitt.analysis import MeasSchmitt

    raw = _run_schmitt_sim(run_dir, tb)
    interval = tb.waveform_sample_interval_s
    wave, points = read_transient_wave(raw, schmitt_signal_names(), interval, supply_rails=("vdd",))
    measurement = MeasSchmitt(
        group=None,
        index=None,
        dut=tb.schmitt,
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


def _transfer(inp: np.ndarray, out: np.ndarray, levels: np.ndarray) -> tuple[list[float], list[float]]:
    """The output at each input level on the triangle's way up and on its way down."""

    peak = int(np.argmax(inp))
    curves = []
    for x, y in ((inp[: peak + 1], out[: peak + 1]), (inp[peak:][::-1], out[peak:][::-1])):
        rising = np.diff(x, prepend=-np.inf) > 0  # the ramp alone, without the rests
        curves.append(list(np.interp(levels, x[rising], y[rising])))
    return curves[0], curves[1]


def characterize(run_dir: Path, pdk: str, schmitt: SchmittParams) -> Record:
    from flow.analysis.io import write_measurement
    from flow.schmitt.analysis import analyze_schmitt_delay, analyze_schmitt_trip

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    triangles, steps = [], []
    for factor in SUPPLY_SWEEP:
        vdd, point = round(factor * supply, 4), f"vdd{round(factor * 100)}"
        triangles.append(_measure(run_dir / f"triangle_{point}", SchmittTbParams(pdk=pdk, schmitt=schmitt, vdd=vdd)))
        steps.append(
            _measure(
                run_dir / f"step_{point}",
                SchmittTbParams(pdk=pdk, schmitt=schmitt, vdd=vdd, step=True, waveform_sample_interval_s=1e-12),
            )
        )
    nominal = SUPPLY_SWEEP.index(1.0)
    waves = {}
    for name, folder, measurement in (
        ("triangle", "triangle_vdd100", triangles[nominal]),
        ("step", "step_vdd100", steps[nominal]),
    ):
        path = run_dir / folder / "result.h5"
        write_measurement(path, measurement)
        waves[name] = str(path.relative_to(Path(__file__).resolve().parents[2]))

    # both in the supply sweep's (ascending) order
    trip = analyze_schmitt_trip(triangles)
    delay = analyze_schmitt_delay(steps)
    levels = np.linspace(0.0, supply, TRANSFER_POINTS)
    up, down = _transfer(trip.inp_v[nominal], trip.out_v[nominal], levels)

    return Record(
        metrics={
            "rise_trip_v": float(trip.rise_trip_v[nominal]),
            "fall_trip_v": float(trip.fall_trip_v[nominal]),
            "hysteresis_v": float(trip.hysteresis_v[nominal]),
            "delay_rise_s": float(delay.rise_delay_s[nominal]),
            "delay_fall_s": float(delay.fall_delay_s[nominal]),
            "transition_rise_s": float(delay.out_rise_time_s[nominal]),
            "transition_fall_s": float(delay.out_fall_time_s[nominal]),
            "energy_per_cycle_j": float(delay.energy_per_cycle_j[nominal]),
            "hysteresis_min_supply_v": float(np.nanmin(trip.hysteresis_v)),
            "delay_max_supply_s": float(np.nanmax([delay.rise_delay_s, delay.fall_delay_s])),
        },
        details=[
            Detail(
                name="transfer",
                title="Transfer on the triangle (nominal supply)",
                x_label="Input (V)",
                y_label="Output (V)",
                x=list(levels),
                series={"input rising": up, "input falling": down},
            ),
            Detail(
                name="trip_supply",
                title="Trip points over the supply",
                x_label="Supply over nominal",
                y_label="Input at the switch (V)",
                x=list(SUPPLY_SWEEP),
                series={"input rising": list(trip.rise_trip_v), "input falling": list(trip.fall_trip_v)},
            ),
            Detail(
                name="hysteresis_supply",
                title="Hysteresis over the supply",
                x_label="Supply over nominal",
                y_label="Hysteresis (V)",
                x=list(SUPPLY_SWEEP),
                series={"hysteresis": list(trip.hysteresis_v)},
            ),
            Detail(
                name="delay_supply",
                title="Delay over the supply (5 fF)",
                x_label="Supply over nominal",
                y_label="Delay (s)",
                x=list(SUPPLY_SWEEP),
                series={"input rising": list(delay.rise_delay_s), "input falling": list(delay.fall_delay_s)},
            ),
            Detail(
                name="energy_supply",
                title="Energy per step cycle over the supply",
                x_label="Supply over nominal",
                y_label="Energy per cycle (J)",
                x=list(SUPPLY_SWEEP),
                series={"energy": list(delay.energy_per_cycle_j)},
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, schmitt: SchmittParams) -> Path:
    """The all-transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``)."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(schmitt, out_dir / "schmitt_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "schmitt.sp")
