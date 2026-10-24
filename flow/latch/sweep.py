"""The latch's design space (``flow.sweep``): the characterization's nine latches, flip-flops,
dividers and SR latches at up to six sizes, in every PDK.

Each instance at the core supply (2 ns clock, data 0.5 ns before each capturing edge; an SR
latch's set and reset 5.2 ns apart): the rising and falling delays to q (clk, or s and r) and the
energy per cycle, and the same over the supply (90 to 120 % of its own). A latch or flip-flop
over the data offset (-200 to 300 ps in 25 ps steps): setup at a 10 % delay pushout, and hold. A
flip-flop or divider over the clock period (1 ns to 30 ps): the highest frequency at which every
edge captures (a divider's: toggles). A C2MOS or DICE latch without reset struck while holding a
1 (1 to 200 fC on its storage node): q's dip and the critical charge. Four to 35 Spectre runs,
up to two minutes.
"""

from __future__ import annotations

import importlib
import math
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.pipeline import Plot, Record

from .sim import UPSET_NODE, LatchTbParams, _run_latch_sim, latch_signal_names
from .subckt import CASES, CLOCKED_STYLES, Latch, LatchParams, Style, is_valid_latch_params, write_netlist

GENERATOR = Latch
# the characterization's latches, flip-flops, dividers and SR latches (flow.latch.subckt.CASES)
STRUCTURE = ("style", "flop", "divider", "reset")
STRUCTURES = [{key: getattr(case, key) for key in STRUCTURE} for case in CASES.values()]
# every width scaled together (x0.5 to x4), the feedback (DICE: storage) devices alone doubled
# (not in a TSPC or SR latch, which have none), and every device at twice its length
NOMINAL = LatchParams()
WIDTHS = ("n_w", "p_w", "fb_n_w", "fb_p_w")
FEEDBACK = {name: 2 * getattr(NOMINAL, name) for name in ("fb_n_w", "fb_p_w")}
SIZES = [
    {name: max(1, getattr(NOMINAL, name) // 2) for name in WIDTHS},
    {},
    {name: 2 * getattr(NOMINAL, name) for name in WIDTHS},
    {name: 4 * getattr(NOMINAL, name) for name in WIDTHS},
    FEEDBACK,
    {"l": 2 * NOMINAL.l},
]
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
DATA_OFFSET_SWEEP_S = tuple(round(offset * 1e-12, 15) for offset in range(-200, 301, 25))
PERIOD_SWEEP_S = (1e-9, 500e-12, 300e-12, 200e-12, 150e-12, 100e-12, 70e-12, 50e-12, 30e-12)
UPSET_CHARGES_C = tuple(charge * 1e-15 for charge in (1, 2, 3, 5, 7, 10, 20, 50, 100, 200))


def instances(pdk: str) -> list[LatchParams]:
    """Every latch at every size it has devices for (feedback devices only in the clocked and DICE
    styles), in every PDK."""
    latches = (
        LatchParams(**structure, **sizes)
        for structure in STRUCTURES
        for sizes in SIZES
        if sizes is not FEEDBACK or structure["style"] in (Style.CLOCKED, Style.DICE)
    )
    return [latch for latch in latches if is_valid_latch_params(latch)]


def _measure(run_dir: Path, tb: LatchTbParams):
    """One Spectre run of the latch testbench, as a measurement."""

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave
    from flow.latch.analysis import MeasLatch

    raw = _run_latch_sim(run_dir, tb)
    interval = tb.waveform_sample_interval_s
    wave, points = read_transient_wave(raw, latch_signal_names(), interval, supply_rails=("vdd",))
    measurement = MeasLatch(
        group=None,
        index=None,
        dut=tb.latch,
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


def characterize(run_dir: Path, pdk: str, latch: LatchParams) -> Record:
    from flow.analysis.io import write_measurement
    from flow.latch.analysis import (
        analyze_latch_constraint,
        analyze_latch_sr,
        analyze_latch_timing,
        analyze_latch_upset,
    )

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    clocked = latch.style in CLOCKED_STYLES
    root = Path(__file__).resolve().parents[2]
    waves = {}

    def keep(name: str, folder: str, measurement) -> None:
        path = run_dir / folder / "result.h5"
        write_measurement(path, measurement)
        waves[name] = str(path.relative_to(root))

    supplies = [
        _measure(
            run_dir / f"supply_{round(factor * 100)}",
            LatchTbParams(pdk=pdk, latch=latch, vdd=round(factor * supply, 4)),
        )
        for factor in SUPPLY_SWEEP
    ]
    at = SUPPLY_SWEEP.index(1.0)
    keep("nominal", "supply_100", supplies[at])
    if clocked:
        over_supply = analyze_latch_timing(supplies)
        rise, fall = over_supply.clock_to_q_rise_s, over_supply.clock_to_q_fall_s
    else:
        over_supply = analyze_latch_sr(supplies)
        rise, fall = over_supply.set_delay_s, over_supply.reset_delay_s
    energy = over_supply.energy_per_cycle_j
    metrics = {
        "delay_rise_s": float(rise[at]),
        "delay_fall_s": float(fall[at]),
        "energy_per_cycle_j": float(energy[at]),
        "delay_max_supply_s": float(np.nanmax([rise, fall])),
        "setup_s": math.nan,
        "hold_s": math.nan,
        "fmax_hz": math.nan,
        "critical_charge_c": math.nan,
    }
    cycle = "clock cycle" if clocked else "set and reset cycle"
    details = [
        Plot(
            name="delay_supply",
            title=f"Delay to q over the supply ({'2 ns clock' if clocked else 'set and reset'})",
            x_label="Supply over nominal",
            y_label="Delay (s)",
            x=list(SUPPLY_SWEEP),
            series={"q rising": list(rise), "q falling": list(fall)},
        ),
        Plot(
            name="energy_supply",
            title=f"Energy per {cycle} over the supply",
            x_label="Supply over nominal",
            y_label="Energy per cycle (J)",
            x=list(SUPPLY_SWEEP),
            series={"energy": list(energy)},
        ),
    ]

    if clocked and not latch.divider:
        offsets = [
            _measure(
                run_dir / f"offset_{round(offset * 1e12)}ps",
                LatchTbParams(pdk=pdk, latch=latch, vdd=supply, data_offset_s=offset),
            )
            for offset in DATA_OFFSET_SWEEP_S
        ]
        over_offset = analyze_latch_timing(offsets)
        constraint = analyze_latch_constraint(offsets, timing=over_offset)
        metrics |= {"setup_s": constraint.setup_s, "hold_s": constraint.hold_s}
        details += [
            Plot(
                name="delay_offset",
                title="Delay to q over the data offset before the capturing edge (setup and hold)",
                x_label="Data offset (s)",
                y_label="Delay (s)",
                x=list(DATA_OFFSET_SWEEP_S),
                series={
                    "q rising": list(over_offset.clock_to_q_rise_s),
                    "q falling": list(over_offset.clock_to_q_fall_s),
                },
            ),
            Plot(
                name="capture_offset",
                title="Edges taking the new value or keeping the old over the data offset",
                x_label="Data offset (s)",
                y_label="Share of edges",
                x=list(DATA_OFFSET_SWEEP_S),
                series={"captured": list(over_offset.captured_fraction), "held": list(over_offset.held_fraction)},
            ),
        ]

    if latch.flop:
        # the edges and the data offset scale with a short clock, as in the characterization
        periods = [
            _measure(
                run_dir / f"period_{round(period * 1e12)}ps",
                LatchTbParams(
                    pdk=pdk,
                    latch=latch,
                    vdd=supply,
                    clock_period_s=period,
                    transition_time_s=min(50e-12, period / 8),
                    data_offset_s=period / 4,
                    reset_time_s=max(0.5e-9, 2 * period),
                    cycles=12,
                ),
            )
            for period in PERIOD_SWEEP_S
        ]
        over_period = analyze_latch_timing(periods)
        frequency = 1 / over_period.clock_period_s
        working = frequency[over_period.captured_fraction == 1.0]
        metrics["fmax_hz"] = float(np.max(working)) if len(working) else math.nan
        details += [
            Plot(
                name="capture_frequency",
                title="Edges captured over the clock frequency" + (" (toggling)" if latch.divider else ""),
                x_label="Clock frequency (Hz)",
                y_label="Share of edges",
                x=list(frequency),
                series={"captured": list(over_period.captured_fraction)},
                x_log=True,
            ),
            Plot(
                name="delay_frequency",
                title="Delay to q over the clock frequency",
                x_label="Clock frequency (Hz)",
                y_label="Delay (s)",
                x=list(frequency),
                series={
                    "q rising": list(over_period.clock_to_q_rise_s),
                    "q falling": list(over_period.clock_to_q_fall_s),
                },
                x_log=True,
            ),
        ]

    if latch.style in UPSET_NODE and not (latch.flop or latch.reset):
        strikes = [
            _measure(
                run_dir / f"upset_{round(charge * 1e15)}fc",
                LatchTbParams(pdk=pdk, latch=latch, vdd=supply, upset_charge_c=charge),
            )
            for charge in UPSET_CHARGES_C
        ]
        upset = analyze_latch_upset(strikes)
        metrics["critical_charge_c"] = upset.critical_charge_c
        # the strike that flips it, or the strongest one where none does
        shown = upset.critical_charge_c if math.isfinite(upset.critical_charge_c) else UPSET_CHARGES_C[-1]
        index = int(np.argmin(np.abs(np.asarray(UPSET_CHARGES_C) - shown)))
        keep(f"{round(shown * 1e15)} fC strike", f"upset_{round(shown * 1e15)}fc", strikes[index])
        details += [
            Plot(
                name="upset_dip",
                title="q's dip after a strike on the storage node (holding a 1)",
                x_label="Charge (C)",
                y_label="q's dip (V)",
                x=list(upset.charge_c),
                series={"dip": list(upset.q_dip_v)},
                x_log=True,
            ),
            Plot(
                name="upset_flip",
                title="Whether a strike flips the held 1",
                x_label="Charge (C)",
                y_label="Flipped",
                x=list(upset.charge_c),
                series={"flipped": list(upset.upset)},
                x_log=True,
            ),
        ]

    return Record(metrics=metrics, details=details, waves=waves)


def layout_netlist(out_dir: Path, pdk: str, latch: LatchParams) -> Path:
    """The all-transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``)."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(latch, out_dir / "latch_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "latch.sp")
