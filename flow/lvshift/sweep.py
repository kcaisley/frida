"""The level shifters' design space (``flow.sweep``): the characterization's three shifters at
seven sizes, in every PDK.

Each instance at the nominal supplies (its own core supply out, two thirds of it in): the rise
and fall delays, the share of input edges followed, the output levels, the energy per input
period from both supplies and the idle current. Over the input supply (a quarter of the core
supply to all of it) the delays, energy and idle current, and the lowest input supply it still
follows; over the output supply (90 to 120 % of its own, the input fixed) the delays and idle
current. Thirteen Spectre runs, under a minute in all.
"""

from __future__ import annotations

import importlib
import math
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.pipeline import Plot, Record

from .sim import NOMINAL_VDDL, VDDL_SWEEP, LvShiftTbParams, _run_lvshift_sim, lvshift_signal_names
from .subckt import CASES, LvShift, LvShiftParams, is_valid_lvshift_params, write_netlist

GENERATOR = LvShift
# the characterization's shifters (flow.lvshift.subckt.CASES)
STRUCTURE = ("input_inverter", "reset", "buffers")
STRUCTURES = [{key: getattr(case, key) for key in STRUCTURE} for case in CASES.values()]
# the key devices' widths scaled together (x0.5 to x4), the input pair or the cross-coupled pair
# alone doubled (the ratio the input pair must win), and the cross-coupled pair at twice its length
DEFAULT = LvShiftParams()
WIDTHS = ("in_w", "cross_w", "inv_n_w", "inv_p_w")
SIZES = [
    {name: getattr(DEFAULT, name) // 2 for name in WIDTHS},
    {},
    {name: 2 * getattr(DEFAULT, name) for name in WIDTHS},
    {name: 4 * getattr(DEFAULT, name) for name in WIDTHS},
    {"in_w": 2 * DEFAULT.in_w},
    {"cross_w": 2 * DEFAULT.cross_w},
    {"cross_l": 2 * DEFAULT.cross_l},
]
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)


def instances(pdk: str) -> list[LvShiftParams]:
    """Every shifter at every size, in every PDK."""
    shifters = (LvShiftParams(**structure, **sizes) for structure in STRUCTURES for sizes in SIZES)
    return [lvshift for lvshift in shifters if is_valid_lvshift_params(lvshift)]


def _measure(run_dir: Path, tb: LvShiftTbParams):
    """One Spectre transient of the level shifter testbench, as a measurement."""

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave

    from .analysis import MeasLvShift

    # without output inverters bufp and bufn hold only their loads, and Spectre saves no trace
    buffered = ("bufp", "bufn")
    names = {raw: name for raw, name in lvshift_signal_names().items() if tb.lvshift.buffers or name not in buffered}
    raw = _run_lvshift_sim(run_dir, tb)
    wave, points = read_transient_wave(raw, names, tb.waveform_sample_interval_s, supply_rails=("vdd", "vddl"))
    info = MeasInfo(
        backend="spice",
        timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
        instruments={"simulator": "Spectre"},
        readbacks={"raw_points": points, "supply_current_convention": "positive_current_draw"},
    )
    raw.unlink()  # the measurement keeps the waveforms
    return MeasLvShift(
        group=None, index=None, dut=tb.lvshift, info=info, param=tb, trial_index=np.arange(1, dtype=np.int64), wave=wave
    )


def characterize(run_dir: Path, pdk: str, lvshift: LvShiftParams) -> Record:
    from flow.analysis.io import write_measurement

    from .analysis import analyze_lvshift_switching

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    vddl = NOMINAL_VDDL * supply

    def point(folder: str, vdd: float, vddl: float):
        return _measure(
            run_dir / folder, LvShiftTbParams(pdk=pdk, lvshift=lvshift, vdd=round(vdd, 4), vddl=round(vddl, 4))
        )

    inputs = {step: point(f"vddl_{round(step * 24)}of24", supply, step * supply) for step in VDDL_SWEEP}
    nominal = inputs[NOMINAL_VDDL]
    outputs = {
        factor: nominal if factor == 1.0 else point(f"vdd_{round(factor * 100)}", factor * supply, vddl)
        for factor in SUPPLY_SWEEP
    }
    waves = {}
    for label, step in (("input supply 2/3", NOMINAL_VDDL), ("input supply 5/12", 10 / 24)):
        path = run_dir / f"vddl_{round(step * 24)}of24" / "result.h5"
        write_measurement(path, inputs[step])
        waves[label] = str(path.relative_to(Path(__file__).resolve().parents[2]))
    over_input = analyze_lvshift_switching(list(inputs.values()))
    over_output = analyze_lvshift_switching(list(outputs.values()))
    at = analyze_lvshift_switching([nominal])
    # following every edge: both delays defined
    follows = np.isfinite(over_input.rise_delay_s) & np.isfinite(over_input.fall_delay_s)
    delays = np.concatenate([over_output.rise_delay_s, over_output.fall_delay_s])
    input_v = list(over_input.vddl_v)

    return Record(
        metrics={
            "rise_delay_s": float(at.rise_delay_s[0]),
            "fall_delay_s": float(at.fall_delay_s[0]),
            "switched_fraction": float(at.switched_fraction[0]),
            "output_high_v": float(at.output_high_v[0]),
            "output_low_v": float(at.output_low_v[0]),
            "energy_per_cycle_j": float(at.energy_per_cycle_j[0]),
            "static_current_a": float(at.static_current_a[0]),
            "vddl_min_v": float(np.min(over_input.vddl_v[follows])) if follows.any() else math.nan,
            "delay_max_supply_s": float(np.nanmax(delays)) if np.isfinite(delays).any() else math.nan,
        },
        details=[
            Plot(
                name="delay_vddl",
                title="Delay over the input supply (core supply out)",
                x_label="Input supply (V)",
                y_label="Delay (s)",
                x=input_v,
                series={"rise": list(over_input.rise_delay_s), "fall": list(over_input.fall_delay_s)},
            ),
            Plot(
                name="energy_vddl",
                title="Energy per input period over the input supply (both supplies)",
                x_label="Input supply (V)",
                y_label="Energy per period (J)",
                x=input_v,
                series={"energy": list(over_input.energy_per_cycle_j)},
            ),
            Plot(
                name="idle_vddl",
                title="Idle supply current over the input supply",
                x_label="Input supply (V)",
                y_label="Idle current (A)",
                x=input_v,
                series={"idle": list(over_input.static_current_a)},
                y_log=True,
            ),
            Plot(
                name="delay_supply",
                title="Delay over the output supply (input supply fixed)",
                x_label="Output supply over nominal",
                y_label="Delay (s)",
                x=list(SUPPLY_SWEEP),
                series={"rise": list(over_output.rise_delay_s), "fall": list(over_output.fall_delay_s)},
            ),
            Plot(
                name="idle_supply",
                title="Idle supply current over the output supply",
                x_label="Output supply over nominal",
                y_label="Idle current (A)",
                x=list(SUPPLY_SWEEP),
                series={"idle": list(over_output.static_current_a)},
                y_log=True,
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, lvshift: LvShiftParams) -> Path:
    """The transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``: the output inverters; the input inverter, on vddl, stays
    transistors), for ALIGN to lay out without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(lvshift, out_dir / "lvshift_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "lvshift.sp")
